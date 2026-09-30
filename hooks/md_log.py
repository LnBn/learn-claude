#!/usr/bin/env python3
"""
md-log — mirror the session to a markdown file for comfortable reading.

Port of the pi `md-log` extension to Claude Code hooks. Designed for long
teaching sessions where the terminal is hard on the eyes and markdown/math/code
don't render. The linked .md file is meant to be viewed rendered (e.g. in
Obsidian), so assistant text with $...$ math, code blocks and markdown all
render natively — no rendering work here.

Captures only reading-relevant content:
  - user prompts                           (> [!quote] YOU)
  - assistant text (lesson prose)          (written bare, no banner) — minus session narration
                                            ("I'll load the skill", "waiting on your answer"), see is_narration
  - AskUserQuestion Q&A blocks             (> [!question] Question  +  > [!example] Answer)
  - graded quiz tool blocks                (> [!question] Quiz  +  ✓/✗ result) — the quiz MCP server
                                            writes these itself, live; the Stop replay only backfills
  - a dated session header                 (---  ## Session — 2026-09-30 (Wed) 14:05) the first time a
                                            session writes to the file, and "Session (continued)" if the
                                            same session writes again on a later day
Other tools (Bash, Read, Edit, Agent, ...) are omitted.

Wiring (see settings.json):
  UserPromptSubmit          -> logs the prompt live
  PostToolUse:AskUserQuestion -> logs the question + answer live
  Stop                      -> reads the session transcript from a per-session
                               cursor and logs everything not yet logged
                               (assistant prose; and, on a fresh link, the
                               whole history = backfill)

Commands (called by the /md-log and /md-unlog skills):
  md_log.py link <file> [--session ID]   link a file (resets the cursor -> backfill on next Stop)
  md_log.py unlink                       stop logging
  md_log.py status
  md_log.py rebuild <out.md> <transcript.jsonl>...
                                         regenerate a lesson file from session transcripts
                                         (in the order given) with the current filters

State lives next to this script's .claude dir:
  <project>/.claude/md-log.json              {"file": "/abs/path.md"}
  <project>/.claude/md-log-state/<session>.json   {"line": N, "prompts": [...], "tool_ids": [...], "file": ...}
  (the session's own file wins over md-log.json, so two sessions can log to two notes;
   the quiz server only knows md-log.json, i.e. the most recently linked file)

NOTE: the transcript JSONL is an internal Claude Code format and may change
between versions; parsing here is defensive and fails silently (never blocks
the session).
"""
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)  # .../.claude
CONFIG = os.path.join(CLAUDE_DIR, "md-log.json")
STATE_DIR = os.path.join(CLAUDE_DIR, "md-log-state")
QUIZ_LOGGED = os.path.join(STATE_DIR, "quiz-logged.json")  # written by mcp/quiz_server.py
QUIZ_HEADER = "quiz"
QUIZ_TOOL = "mcp__quiz__quiz"


# ---------------------------------------------------------------- config/state

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    data = {k: v for k, v in data.items() if not k.startswith("_")}  # drop scratch fields
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


OUT_OVERRIDE = None  # set by `rebuild` to write somewhere other than the linked file


SESSION_FILE = None  # set per hook invocation from the session state (link --session)


def log_file():
    if OUT_OVERRIDE:
        return OUT_OVERRIDE
    if SESSION_FILE:
        return SESSION_FILE
    return load_json(CONFIG, {}).get("file")


def state_path(session_id):
    return os.path.join(STATE_DIR, f"{session_id or 'unknown'}.json")


def load_state(session_id):
    st = load_json(state_path(session_id), {})
    st.setdefault("line", 0)
    st.setdefault("prompts", [])
    st.setdefault("tool_ids", [])
    return st


def h(text):
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- formatting

def callout(kind, title, body_lines):
    lines = [f"> [!{kind}] {title}", ">"]
    for line in body_lines:
        for sub in str(line).split("\n"):
            lines.append(f"> {sub}" if sub else ">")
    return "\n".join(lines)


def user_block(text):
    return f"> [!quote] YOU\n\n{text}"


def assistant_block(text):
    return text  # the teacher's prose is the lesson itself; no banner


def question_block(q):
    header = (q.get("header") or "").strip()
    is_quiz = header.lower() == QUIZ_HEADER
    title = "Quiz" if is_quiz else (f"Question — {header}" if header else "Question")
    body = [q.get("question", "").strip(), ""]
    for i, o in enumerate(q.get("options") or [], 1):
        label = (o.get("label") or "").strip()
        desc = (o.get("description") or "").strip()
        body.append(f"{i}. {label}" + (f" — {desc}" if desc and not is_quiz else ""))
    if q.get("multiSelect"):
        body.append("")
        body.append("(select all that apply)")
    return callout("question", title, body)


def answer_block(q, selected, other, note):
    options = q.get("options") or []
    labels = [(o.get("label") or "").strip() for o in options]
    body = []
    for s in selected:
        s = str(s).strip()
        if s in labels:
            body.append(f"{labels.index(s) + 1}. {s}")
        else:
            body.append(f"Other: {s}")
    if other:
        body.append(f"Other: {other}")
    if note:
        body.append("")
        body.append(f"Note: {note}")
    if not body:
        body = ["(no answer)"]
    return callout("example", "Answer", body)


# ---- graded quiz tool (mcp/quiz_server.py) — formatting kept in sync with the server

def quiz_question_block(r):
    body = [r["question"]]
    if r.get("details"):
        body += ["", r["details"]]
    body.append("")
    body += [f"{o['index']}. {o['label']}" for o in r["options"]]
    if r.get("multiSelect"):
        body += ["", "(select all that apply)"]
    return callout("question", "Quiz", body)


def quiz_result_block(r):
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
        selected = ", ".join(f"{i}. {by_index[i]}" for i in r.get("answers", []))
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


def quiz_blocks_from_result(text):
    """Parse the QUIZ_JSON line the quiz tool appends to its result."""
    if not isinstance(text, str) or "QUIZ_JSON:" not in text:
        return ""
    try:
        r = json.loads(text.split("QUIZ_JSON:", 1)[1].strip().splitlines()[0])
    except Exception:
        return ""
    return quiz_question_block(r) + "\n\n" + quiz_result_block(r)


def ensure_session_header(state, when=None):
    """Separate sessions visibly in the file: a rule + dated H2 on a session's first write."""
    when = when if when is not None else time.localtime()
    today = time.strftime("%Y-%m-%d", when)
    if state.get("header_date") == today:
        return
    label = "Session (continued)" if state.get("header_date") else "Session"
    append(f"---\n\n## {label} — {time.strftime('%Y-%m-%d (%a) %H:%M', when)}")
    state["header_date"] = today


def transcript_start(path):
    """Local time of the first user prompt in a transcript, for rebuild headers."""
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                try:
                    e = json.loads(raw)
                except Exception:
                    continue
                if e.get("type") == "user" and e.get("timestamp"):
                    ts = e["timestamp"].replace("Z", "+00:00")
                    from datetime import datetime
                    return datetime.fromisoformat(ts).astimezone().timetuple()
    except Exception:
        pass
    return None


def append(text):
    path = log_file()
    if not path or not text.strip():
        return
    try:
        current = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                current = f.read()
        prefix = "\n\n" if current.strip() else ""
        with open(path, "a", encoding="utf-8") as f:
            f.write(prefix + text.rstrip("\n") + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- cleaning

NOISE_TAGS = ("system-reminder", "command-message", "command-args", "local-command-stdout",
              "local-command-caveat", "ide_opened_file", "ide_selection", "pasted_content",
              "task-notification", "agent-message", "tool_use_error")


def clean_user_text(text):
    """Drop harness-injected context; return '' if nothing user-written remains."""
    if not isinstance(text, str):
        return ""
    if "<command-name>" in text:  # a slash command / skill invocation, not prose
        return ""
    for tag in NOISE_TAGS:
        text = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}>", "", text, flags=re.S)
    text = re.sub(r"<[a-z_-]+\b[^>]*>\s*</[a-z_-]+>", "", text)
    text = text.strip()
    # anything still wrapped entirely in a tag is harness-injected, not prose
    if re.fullmatch(r"<([a-z_-]+)\b[^>]*>.*</\1>", text, flags=re.S):
        return ""
    return text


def is_user_prose(text):
    return bool(text) and not text.startswith("/")


SKIP_ASSISTANT = re.compile(r"^\s*🗒 md-log")

# The lesson file must read like a lesson, not like a Claude Code session. Assistant text that
# only narrates the session ("I'll load the teach skill", "waiting on your answer", "the researcher
# is scoping the topic") is dropped:
#   - short text that shares an API message with a tool call (that text is the preamble to the call)
#   - short standalone text that starts like narration
NARRATION_MAX = 300
NARRATION_RE = re.compile(
    r"^\s*(I'll|I will|I'm going|I am going|Let me|Let's (load|start|check|run)|Now I|Next I|First I|"
    r"Loading|Waiting|While (that|the)|Once (the|that|its)|One moment|Give me a moment|"
    r"The (researcher|maker|brief|subagent|diagram) (is|has|came|comes)|Got it|Understood|Sure[,.]|"
    r"Okay[,.]|OK[,.]|Great[,.!]|Perfect[,.!]|Still |The (first|next|last|second) (quiz|question|check))",
    re.I,
)
NARRATION_ANY_RE = re.compile(
    r"(waiting (on|for) your (answer|reply|response)|I'll hold here|hold here until|"
    r"once (it|that|the \w+) (comes|is) back|will follow it|before asking the next)",
    re.I,
)


def is_narration(text, shares_message_with_tool):
    t = text.strip()
    if len(t) > NARRATION_MAX:
        return False
    if shares_message_with_tool:
        return True
    return bool(NARRATION_RE.match(t) or NARRATION_ANY_RE.search(t))


# ---------------------------------------------------------------- answers

def parse_answers(tool_input, tool_response):
    """Return list of (question_dict, selected_labels, other_text, note) for one call.

    Handles the shapes seen so far:
      {"answers": {"<question>": "<label or free text>"}, "annotations": {"<question>": {"notes": ...}}}
      {"answers": [{"question": ..., "selected": [...], "other": ...}]}
      a plain string result
    """
    questions = (tool_input or {}).get("questions") or []
    answers = None
    annotations = {}
    if isinstance(tool_response, dict):
        answers = tool_response.get("answers")
        annotations = tool_response.get("annotations") or {}
    elif isinstance(tool_response, str):
        m = re.findall(r'"((?:[^"\\]|\\.)*)"="((?:[^"\\]|\\.)*)"', tool_response)
        if m:
            answers = {k.replace('\\"', '"'): v.replace('\\"', '"') for k, v in m}
    out = []
    for q in questions:
        qt = q.get("question", "")
        selected, other, note = [], "", ""
        if isinstance(answers, dict):
            val = answers.get(qt)
            if isinstance(val, list):
                selected = [str(v) for v in val]
            elif val is not None:
                val = str(val)
                # multiSelect answers arrive comma-joined
                labels = [(o.get("label") or "").strip() for o in (q.get("options") or [])]
                if q.get("multiSelect") and ", " in val and all(p.strip() in labels for p in val.split(", ")):
                    selected = [p.strip() for p in val.split(", ")]
                else:
                    selected = [val]
            ann = annotations.get(qt) if isinstance(annotations, dict) else None
            if isinstance(ann, dict):
                note = str(ann.get("notes") or "").strip()
        elif isinstance(answers, list):
            for a in answers:
                if isinstance(a, dict) and a.get("question") == qt:
                    sel = a.get("selected")
                    selected = [str(s) for s in sel] if isinstance(sel, list) else ([str(sel)] if sel else [])
                    other = str(a.get("other") or "").strip()
                    note = str(a.get("notes") or "").strip()
        out.append((q, selected, other, note))
    return out


def qa_blocks(tool_input, tool_response):
    blocks = []
    for q, selected, other, note in parse_answers(tool_input, tool_response):
        blocks.append(question_block(q))
        blocks.append(answer_block(q, selected, other, note))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------- transcript replay

def wait_for_transcript(path, start_line, max_wait=8.0):
    """The Stop hook can fire before Claude Code has flushed the final assistant
    message to the transcript. Wait until an assistant entry exists after the
    cursor and the file has stopped growing, or give up after max_wait."""
    deadline = time.time() + max_wait
    last_size, stable_since = -1, None
    while time.time() < deadline:
        try:
            size = os.path.getsize(path)
        except Exception:
            return
        if size != last_size:
            last_size, stable_since = size, time.time()
        elif time.time() - stable_since >= 0.5:
            try:
                with open(path, encoding="utf-8") as f:
                    tail = f.readlines()[start_line:]
            except Exception:
                return
            if any('"type":"assistant"' in ln or '"type": "assistant"' in ln for ln in tail):
                return
        time.sleep(0.15)


def replay_transcript(path, state):
    """Log everything after state['line']; return number of blocks written."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return 0
    start = state.get("line", 0)
    if start > len(lines):  # transcript rewritten (e.g. compaction) — start over
        start = 0
    pending_prompts = set(state.get("prompts", []))
    logged_ids = set(state.get("tool_ids", [])) | set(load_json(QUIZ_LOGGED, []))
    ask_calls = {}  # tool_use_id -> input
    quiz_calls = set()  # tool_use_ids of the graded quiz tool
    written = 0
    blocks = []
    state["_logged_user_keys"] = set()

    # first pass: which API messages contain a tool call (their text is narration, see is_narration)
    tool_msg_ids = set()
    for raw in lines[start:]:
        try:
            e = json.loads(raw)
        except Exception:
            continue
        if e.get("type") == "assistant" and not e.get("isSidechain"):
            msg = e.get("message") or {}
            if any(isinstance(b, dict) and b.get("type") == "tool_use" for b in (msg.get("content") or [])):
                tool_msg_ids.add(msg.get("id"))

    def flush_text(parts, msg_id=None):
        nonlocal written
        text = "\n\n".join(p for p in parts if p.strip())
        if not text.strip() or SKIP_ASSISTANT.match(text):
            return
        if is_narration(text, msg_id in tool_msg_ids):
            return
        blocks.append(assistant_block(text))
        written += 1

    for raw in lines[start:]:
        try:
            e = json.loads(raw)
        except Exception:
            continue
        if e.get("isSidechain") or e.get("isMeta"):
            continue
        t = e.get("type")
        msg = e.get("message") or {}
        content = msg.get("content")
        if t == "user":
            if isinstance(content, str):
                text = clean_user_text(content)
                if is_user_prose(text):
                    key = h(text)
                    if key in pending_prompts:
                        pending_prompts.discard(key)
                    else:
                        blocks.append(user_block(text))
                        state["_logged_user_keys"].add(key)
                        written += 1
            elif isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        text = clean_user_text(b.get("text", ""))
                        if is_user_prose(text):
                            key = h(text)
                            if key in pending_prompts:
                                pending_prompts.discard(key)
                            else:
                                blocks.append(user_block(text))
                                state["_logged_user_keys"].add(key)
                                written += 1
                    elif b.get("type") == "tool_result":
                        tid = b.get("tool_use_id")
                        if tid in ask_calls and tid not in logged_ids:
                            resp = e.get("toolUseResult")
                            if resp is None:
                                resp = b.get("content")
                                if isinstance(resp, list):
                                    resp = "".join(c.get("text", "") for c in resp if isinstance(c, dict))
                            qa = qa_blocks(ask_calls[tid], resp)
                            if qa:
                                blocks.append(qa)
                                written += 1
                            logged_ids.add(tid)
                        elif tid in quiz_calls and tid not in logged_ids:
                            resp = b.get("content")
                            if isinstance(resp, list):
                                resp = "".join(c.get("text", "") for c in resp if isinstance(c, dict))
                            qa = quiz_blocks_from_result(resp)
                            if qa:
                                blocks.append(qa)
                                written += 1
                            logged_ids.add(tid)
        elif t == "assistant" and isinstance(content, list):
            parts = []
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                elif b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
                    ask_calls[b.get("id")] = b.get("input") or {}
                elif b.get("type") == "tool_use" and b.get("name") == QUIZ_TOOL:
                    quiz_calls.add(b.get("id"))
            flush_text(parts, msg.get("id"))

    for blk in blocks:
        append(blk)
    state["line"] = len(lines)
    state["prompts"] = sorted(pending_prompts)
    state["tool_ids"] = sorted(logged_ids)[-400:]
    return written


# ---------------------------------------------------------------- entry points

def handle_hook():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    event = data.get("hook_event_name")
    session = data.get("session_id")
    state = load_state(session)
    global SESSION_FILE
    SESSION_FILE = state.get("file")  # a session linked with --session keeps its own file
    if state.get("file") is None and log_file():
        state["file"] = log_file()  # adopt the project default the first time this session writes
        SESSION_FILE = state["file"]
    if not log_file():
        return
    ensure_session_header(state)

    tp = data.get("transcript_path")

    if event == "UserPromptSubmit":
        text = clean_user_text(data.get("prompt") or "")
        key = h(text) if is_user_prose(text) else None
        logged_by_replay = set()
        if tp and os.path.exists(tp):  # catch anything the last Stop missed
            replay_transcript(tp, state)
            logged_by_replay = state.pop("_logged_user_keys", set())
        if key and key not in logged_by_replay:  # usual case: transcript doesn't have it yet -> log live
            append(user_block(text))
            state["prompts"] = (state["prompts"] + [key])[-50:]  # so the later Stop replay skips it

    elif event == "PostToolUse" and data.get("tool_name") == "AskUserQuestion":
        if tp and os.path.exists(tp):  # prose written earlier this turn goes first
            replay_transcript(tp, state)
        tid = data.get("tool_use_id")
        resp = data.get("tool_response", data.get("tool_output"))
        qa = qa_blocks(data.get("tool_input") or {}, resp)
        if qa:
            append(qa)
            if tid:
                state["tool_ids"] = (state["tool_ids"] + [tid])[-200:]

    elif event == "Stop":
        if tp and os.path.exists(tp):
            wait_for_transcript(tp, state.get("line", 0))
            replay_transcript(tp, state)

    save_json(state_path(session), state)


def main(argv):
    if len(argv) < 2:
        handle_hook()
        return 0
    cmd = argv[1]
    if cmd == "link":
        if len(argv) < 3:
            print("usage: md_log.py link <file.md> [--session ID]", file=sys.stderr)
            return 2
        path = os.path.abspath(os.path.expanduser(argv[2]))
        session = None
        if "--session" in argv:
            session = argv[argv.index("--session") + 1]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            open(path, "a", encoding="utf-8").close()
        save_json(CONFIG, {"file": path})
        if session:
            # reset the cursor so the next Stop hook backfills the whole session; pin the file to this session
            save_json(state_path(session), {"line": 0, "prompts": [], "tool_ids": [], "file": path})
        print(f"🗒 md-log linked: {path}")
        print("The session will be mirrored there (history is backfilled at the end of this turn).")
        return 0
    if cmd == "unlink":
        f = log_file()
        save_json(CONFIG, {"file": None})
        if "--session" in argv:
            sp = state_path(argv[argv.index("--session") + 1])
            st = load_json(sp, {})
            st["file"] = None
            save_json(sp, st)
        print(f"🗒 md-log unlinked" + (f" (was {f})" if f else ""))
        return 0
    if cmd == "status":
        f = log_file()
        print(f"🗒 md-log: {f}" if f else "🗒 md-log: not linked")
        return 0
    if cmd == "rebuild":
        global OUT_OVERRIDE
        if len(argv) < 4:
            print("usage: md_log.py rebuild <out.md> <transcript.jsonl>...", file=sys.stderr)
            return 2
        OUT_OVERRIDE = os.path.abspath(os.path.expanduser(argv[2]))
        open(OUT_OVERRIDE, "w", encoding="utf-8").close()
        global QUIZ_LOGGED
        QUIZ_LOGGED = os.devnull  # every quiz result comes from the transcript in a rebuild
        total = 0
        for tp in argv[3:]:
            state = {"line": 0, "prompts": [], "tool_ids": []}
            ensure_session_header(state, transcript_start(tp))
            total += replay_transcript(tp, state)
        print(f"rebuilt {OUT_OVERRIDE} from {len(argv) - 3} transcript(s): {total} blocks")
        return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as exc:  # never break the session because of the log
        print(f"md-log: {exc}", file=sys.stderr)
        sys.exit(0)
