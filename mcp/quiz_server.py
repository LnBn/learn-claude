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

Options-only: single-select or multi-select. An "I don't know" choice is always
added so the learner can signal a genuine gap instead of guessing. An optional
free-text note travels with any answer.

Logging: if `.claude/md-log.json` links a file, the question block is appended
BEFORE the learner answers (so it appears live, never containing the answer),
and the answer + feedback block after. The tool-use id is recorded in
`.claude/md-log-state/quiz-logged.json` so the md-log Stop hook does not log it
a second time when replaying the transcript.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
POPUP = os.path.join(HERE, "quiz_popup.py")
CLAUDE_DIR = os.path.dirname(HERE)
MDLOG_CONFIG = os.path.join(CLAUDE_DIR, "md-log.json")
STATE_DIR = os.path.join(CLAUDE_DIR, "md-log-state")
QUIZ_LOGGED = os.path.join(STATE_DIR, "quiz-logged.json")
LAST_ASKED = os.path.join(STATE_DIR, "quiz-last-asked.json")  # set when the learner asks before answering
SERVER_LOG = os.path.join(STATE_DIR, "quiz-server.log")
DONT_KNOW = "I don't know"

TOOL = {
    "name": "quiz",
    "description": (
        "Ask the user a GRADED question with a known correct answer, then instantly grade and give feedback. "
        "Unlike AskUserQuestion (which collects preferences/decisions with no right answer), quiz always has a "
        "correct answer supplied by you, marks the user's selection right/wrong (✓/✗), reveals the correct answer, "
        "and shows an explanation. Use it to (1) assess what the learner already understands before teaching, and "
        "(2) run tight practice/retrieval loops after explaining, or probe understanding whenever you're unsure "
        "they've got it. Options-only: single-select or multi-select, plus an automatic 'I don't know' choice so "
        "the user can signal a genuine gap instead of guessing — never add your own opt-out option. An optional "
        "note field lets the user attach free text to ANY answer; it reaches you only when non-empty. "
        "correctAnswer is REQUIRED and is the option `value`, not a position. explanation is REQUIRED. "
        "Options are shuffled before display by default. Make every distractor a specific, believable mistake "
        "(so WHICH wrong answer they pick is diagnostic), keep options even in length/specificity/format so the "
        "right one can't be picked from shape alone, and put zero justification inside any option. "
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
                "description": "The answer options (2 or more). Options only — no free-text mode. Give each a stable `value`; you reference the correct one(s) by that value in correctAnswer.",
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
            "shuffle": {"type": "boolean", "description": "Defaults to true: options are reordered before display. Set false only when order is meaningful (ordered numeric values, or an 'All/None of the above' option that must stay last)."},
        },
        "required": ["question", "options", "correctAnswer", "explanation"],
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


def log_file():
    return load_json(MDLOG_CONFIG, {}).get("file")


def append_log(text):
    path = log_file()
    if not path or not text.strip():
        return
    try:
        current = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                current = f.read()
        prefix = ("\n" if current.endswith("\n") else "\n\n") if current.strip() else ""
        with open(path, "a", encoding="utf-8") as f:
            f.write(prefix + text.strip("\n") + "\n")
    except Exception:
        pass


def diag(msg):
    """Append a line to .claude/md-log-state/quiz-server.log (why a fallback happened, etc.)."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(SERVER_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg.rstrip() + "\n")
    except Exception:
        pass


def save_last_asked(displayed):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LAST_ASKED, "w", encoding="utf-8") as f:
            json.dump({"labels": sorted(o["label"].strip().lower() for o in displayed),
                       "order": [o["label"].strip().lower() for o in displayed]}, f)
    except Exception:
        pass


def clear_last_asked():
    try:
        os.remove(LAST_ASKED)
    except Exception:
        pass


def mark_logged(tool_use_id):
    if not tool_use_id:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        ids = load_json(QUIZ_LOGGED, [])
        ids = (ids + [tool_use_id])[-500:]
        with open(QUIZ_LOGGED, "w", encoding="utf-8") as f:
            json.dump(ids, f)
    except Exception:
        pass


def callout(kind, title, body_lines):
    lines = [f"> [!{kind}] {title}", ">"]
    for line in body_lines:
        for sub in str(line).split("\n"):
            lines.append(f"> {sub}" if sub else ">")
    return "\n".join(lines)


def question_block(r):
    body = [r["question"]]
    if r.get("details"):
        body += ["", r["details"]]
    body.append("")
    body += [f"{o['index']}. {o['label']}" for o in r["options"]]
    if r.get("multiSelect"):
        body += ["", "(select all that apply)"]
    return callout("question", "Quiz", body)


def result_block(r):
    """Shared with hooks/md_log.py (kept in sync by hand)."""
    status = r.get("status")
    if status == "cancelled":
        return callout("warning", "Quiz — cancelled", ["(user skipped)"])
    if status == "unavailable":
        return callout("warning", "Quiz — unavailable", [r.get("message", "")])
    if status == "asked":
        return callout("note", "Asked before answering", [r.get("learnerQuestion", "")])
    by_index = {o["index"]: o["label"] for o in r["options"]}
    correct = ", ".join(f"{i}. {by_index[i]}" for i in r["correctIndices"])
    body = []
    if r.get("dontKnow"):
        kind, title = "info", "I don't know"
        body.append(f"Correct answer: {correct}")
    else:
        selected = ", ".join(f"{i}. {by_index[i]}" for i in r["answers"])
        if r.get("correct"):
            kind, title = "success", "✓ Correct"
            body.append(f"Selected: {selected}")
        else:
            kind, title = "failure", "✗ Incorrect"
            body += [f"Selected: {selected}", f"Correct answer: {correct}"]
    if r.get("explanation"):
        body += ["", r["explanation"]]
    if r.get("note"):
        body += ["", f"Note: {r['note']}"]
    return callout(kind, title, body)


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


def run_quiz(args, tool_use_id):
    question = str(args.get("question", "")).strip()
    details = str(args.get("details") or "").strip()
    options = normalize_options(args.get("options"))
    multi = bool(args.get("multiSelect"))
    shuffle = args.get("shuffle", True) is not False
    explanation = str(args.get("explanation") or "").strip()

    if not question:
        return err("question is required")
    if len(options) < 2:
        return err("quiz needs at least two options")
    if any(o["label"].lower() in {DONT_KNOW.lower(), "i dont know", "not sure", "i'm not sure", "unsure"} for o in options):
        return err("do not add your own 'I don't know' / 'not sure' option — it is added automatically")
    if not explanation:
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

    # A re-ask after "ask the teacher first": same option set as the pending question -> keep the
    # displayed order the learner already saw and do not log the question block again.
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

    # --- show the question (live) before the learner answers (not again on a re-ask)
    if not reask:
        append_log(question_block(record))
    clear_last_asked()

    # --- ask the learner: tmux popup when available (full question + options, like pi),
    #     otherwise Claude Code's elicitation form (which truncates the message to one line)
    ui = ask_via_tmux(record) if tmux_available() else None
    seen_feedback = ui is not None  # the tmux popup shows the grade itself
    if ui is None:
        ui = ask_via_elicitation(record, displayed, msg_details=details, multi=multi)

    if ui.get("action") == "ask":
        q = str(ui.get("question") or "").strip()
        record["status"] = "asked"
        record["learnerQuestion"] = q
        append_log(result_block(record))
        mark_logged(tool_use_id)
        save_last_asked(displayed)
        return result(
            "The learner asked a question BEFORE answering (no answer was given, nothing was graded):\n"
            f"  {q}\n"
            "Answer it now, without giving away the quiz answer. Then call quiz again with the same question, "
            "options, correctAnswer and explanation so they can answer.", record)

    if ui.get("action") != "accept":
        record["status"] = "cancelled"
        append_log(result_block(record))
        mark_logged(tool_use_id)
        return result("User skipped the quiz (cancelled). Ask whether to continue or move on.", record)

    picked = [i for i in ui.get("answers", []) if i in {o["index"] for o in displayed}]
    dont_know = bool(ui.get("dontKnow")) and not picked
    note = str(ui.get("note") or "").strip()
    correct = (not dont_know) and sorted(picked) == correct_indices
    record.update({"answers": picked, "correct": correct, "dontKnow": dont_know, "note": note})

    append_log(result_block(record))
    mark_logged(tool_use_id)

    by_index = {o["index"]: o["label"] for o in displayed}
    correct_str = ", ".join(f"{i}. {by_index[i]}" for i in correct_indices)
    if dont_know:
        text = f"User answered \"I don't know\" — a genuine gap, not a wrong guess.\nCorrect: {correct_str}"
    else:
        sel = ", ".join(f"{i}. {by_index[i]}" for i in picked) or "(nothing)"
        text = f"User answered {'correctly' if correct else 'incorrectly'}.\nSelected: {sel}\nCorrect: {correct_str}"
    text += f"\nExplanation: {explanation}"
    if note:
        text += f"\nNote from user: {note}\nIf this note asks a question, answer it before moving on."
    if seen_feedback:
        text += "\nThe user has already seen this feedback in the popup — do not repeat the grade; continue from it."
    else:
        text += "\nThe user has NOT seen this feedback yet — relay the grade, the correct answer and the explanation in one short block before continuing."
    return result(text, record)


# ----------------------------------------------------------------- learner UI

def tmux_available():
    if not os.environ.get("TMUX"):
        diag("no tmux popup: $TMUX is not set — Claude Code was started outside tmux; using the elicitation form")
        return False
    if shutil.which("tmux") is None:
        diag("no tmux popup: tmux binary not on PATH; using the elicitation form")
        return False
    return True


def ask_via_tmux(record):
    """Show the quiz in a tmux popup. Returns the popup's result dict, or None if
    the popup could not be shown (caller then falls back to elicitation)."""
    work = tempfile.mkdtemp(prefix="learn-quiz.")
    spec_path = os.path.join(work, "spec.json")
    out_path = os.path.join(work, "result.json")
    spec = {"question": record["question"], "details": record.get("details", ""),
            "options": record["options"], "multiSelect": record.get("multiSelect", False),
            "dontKnow": DONT_KNOW, "correctIndices": record["correctIndices"],
            "explanation": record.get("explanation", "")}
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    # size the popup from the content, assuming ~70 usable columns; PgUp/PgDn cover the rest
    def rows(text):
        return sum(max(1, len(par) // 70 + 1) for par in str(text).split("\n")) if text else 0
    n_lines = 9 + rows(record["question"]) + rows(record.get("details")) \
        + sum(rows(o["label"]) for o in record["options"]) + rows(record.get("explanation"))
    height = str(min(max(n_lines, 14), 45))
    cmd = ["tmux", "display-popup", "-E", "-w", "85%", "-h", height, "-T", " quiz ",
           f"{shlex_quote(sys.executable)} {shlex_quote(POPUP)} {shlex_quote(spec_path)} {shlex_quote(out_path)}"]
    try:
        proc = subprocess.run(cmd, check=False, timeout=3600, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
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
        tool_use_id = ((params.get("_meta") or {}).get("claudecode/toolUseId"))
        try:
            res = run_quiz(params.get("arguments") or {}, tool_use_id)
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
