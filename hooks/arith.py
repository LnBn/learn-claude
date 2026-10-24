#!/usr/bin/env python3
"""
arith — timed mental arithmetic sprints (Zetamac-style) in a tmux popup.

The sprint runs on its own, outside the model: questions are generated here, every keypress is checked here, and a
correct answer advances at once. Each question has a kind (`× 7`, `− borrow`, `/16`, …) and its time is recorded,
so `weak` mode can draw from the kinds the learner is slowest at. History: `<vault>/practice/.arith.json`.

    arith.py run [mode] [--seconds 120]     open the popup (tmux), wait for it to close, print the summary
    arith.py play [mode] [--seconds 120]    the sprint itself, in the current terminal (the popup runs this)
    arith.py last                           the summary of the newest sprint
    arith.py history [mode]                 the last 10 complete sprints per mode, best and average
    arith.py kinds [mode]                   every ranked kind's median time, slowest first

Modes: core (default), fractions, powers, estimate, mixed, weak.
"""
import argparse
import json
import os
import random
import shlex
import statistics
import subprocess
import sys
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction

import book

CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.dirname(CLAUDE_DIR)
HISTORY = os.path.join(VAULT, "practice", ".arith.json")

MODES = ("core", "fractions", "powers", "estimate", "mixed", "weak")
CONCRETE = ("core", "fractions", "powers", "estimate")
DENOMINATORS = list(range(2, 13)) + [16, 20, 25, 40]
PERCENTS = (5, 10, 12.5, 15, 20, 25, 30, 40, 75)
TOLERANCE = 0.02
WEAK_SHARE = 0.7
SPEED_WINDOW = 50  # a kind's speed: the median over its last 50 correct answers
RANK_FLOOR = 10  # ranked only with at least this many
WEAK_KINDS = 5


# ---------------------------------------------------------------- questions

def _q(text, answer, kind, mode, estimate=False):
    return {"text": text, "answer": answer, "kind": kind, "mode": mode, "estimate": estimate}


def _shortest(d):
    """A Decimal as its shortest string: 0.3750 -> 0.375, 36.0 -> 36."""
    s = format(d.normalize(), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def core(rng):
    op = rng.choice("+−×÷")
    if op in "+−":
        a, b = rng.randint(2, 100), rng.randint(2, 100)
        if op == "+":
            return _q(f"{a} + {b}", str(a + b), "+ carry" if a % 10 + b % 10 >= 10 else "+ no carry", "core")
        s = a + b  # subtraction is addition reversed
        return _q(f"{s} − {a}", str(b), "− borrow" if s % 10 < a % 10 else "− no borrow", "core")
    a, b = rng.randint(2, 12), rng.randint(2, 100)
    if op == "×":
        return _q(f"{a} × {b}", str(a * b), f"× {a}", "core")
    return _q(f"{a * b} ÷ {a}", str(b), f"÷ {a}", "core")  # division is multiplication reversed


def fractions(rng):
    if rng.random() < 0.5:
        d = rng.choice(DENOMINATORS)
        n = rng.randint(1, d - 1)
        value = (Decimal(n) / Decimal(d)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return _q(f"{n}/{d}", _shortest(value), f"/{d}", "fractions")
    p = rng.choice(PERCENTS)
    while True:
        y = rng.randrange(20, 801, 4)
        value = Fraction(str(p)) * y / 100
        if (value * 10).denominator == 1:  # at most one decimal place
            break
    p_text = f"{p:g}"
    return _q(f"{p_text}% of {y}", _shortest(Decimal(value.numerator) / Decimal(value.denominator)), f"{p_text}% of",
              "fractions")


def powers(rng):
    kind = rng.choice(("square", "2^k", "cube"))
    if kind == "square":
        n = rng.randint(11, 30)
        return _q(f"{n}²", str(n * n), "square 1x" if n < 20 else "square 2x", "powers")
    if kind == "2^k":
        k = rng.randint(5, 20)
        return _q(f"2^{k}", str(2 ** k), "2^k", "powers")
    n = rng.randint(2, 12)
    return _q(f"{n}³", str(n ** 3), "cube", "powers")


def estimate(rng):
    if rng.random() < 0.5:
        while True:
            a, b = rng.randint(12, 999), rng.randint(12, 999)
            if max(a, b) >= 100:
                break
        return _q(f"{a} × {b}", str(a * b), "≈ ×", "estimate", estimate=True)
    a, b = rng.randint(100, 9999), rng.randint(3, 99)
    return _q(f"{a} ÷ {b}", repr(round(a / b, 6)), "≈ ÷", "estimate", estimate=True)


GENERATORS = {"core": core, "fractions": fractions, "powers": powers, "estimate": estimate}


def mode_of(kind):
    if kind.startswith("≈"):
        return "estimate"
    if kind[:1] in "+−×÷":
        return "core"
    if kind.startswith("/") or kind.endswith("% of"):
        return "fractions"
    return "powers"


def of_kind(kind, rng):
    """A question of this kind: drawn from its mode until the kind matches."""
    gen = GENERATORS[mode_of(kind)]
    for _ in range(2000):
        q = gen(rng)
        if q["kind"] == kind:
            return q
    return gen(rng)


def generate(mode, rng, weak_kinds=None):
    if mode == "weak":
        if weak_kinds and rng.random() < WEAK_SHARE:
            slot = rng.randrange(WEAK_KINDS)  # a slot no ranked kind fills is drawn uniformly below
            if slot < len(weak_kinds):
                return of_kind(weak_kinds[slot], rng)
        mode = "mixed"
    if mode == "mixed":
        mode = rng.choice(CONCRETE)
    return GENERATORS[mode](rng)


# ---------------------------------------------------------------- answers

def _number(text):
    try:
        return Decimal(text.strip())
    except (InvalidOperation, ValueError):
        return None


def _places(text):
    return len(text.split(".", 1)[1]) if "." in text else 0


def accepts(typed, q, enter=False):
    """Whether the typed text answers the question: exact answers on any keypress (at full precision), estimates
    on Enter within 2%."""
    v = _number(typed)
    if v is None or not typed.strip():
        return False
    if q.get("estimate"):
        true = Decimal(q["answer"])
        return enter and abs(v - true) <= Decimal(str(TOLERANCE)) * abs(true)
    return v == Decimal(q["answer"]) and _places(typed.strip()) >= _places(q["answer"])


# ---------------------------------------------------------------- history

def load_history():
    if not os.path.exists(HISTORY):
        return {"sprints": []}
    try:
        with open(HISTORY, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("sprints"), list):
            raise ValueError
        return data
    except (OSError, ValueError):
        book.die(f"{book.rel(HISTORY)} cannot be read; fix it or move it away", 1)


def save_sprint(sprint):
    data = load_history()
    data["sprints"].append(sprint)
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    tmp = HISTORY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, HISTORY)


def kind_speeds(history):
    """{kind: median ms over its last 50 correct answers}, for kinds with at least 10."""
    times = {}
    for sp in history["sprints"]:
        for q in sp.get("questions", []):
            times.setdefault(q["kind"], []).append(q["ms"])
    return {k: statistics.median(v[-SPEED_WINDOW:]) for k, v in times.items() if len(v) >= RANK_FLOOR}


def weak_kinds(history):
    """The five kinds slowest relative to the other kinds of their own mode."""
    speeds = kind_speeds(history)
    by_mode = {}
    for k, ms in speeds.items():
        by_mode.setdefault(mode_of(k), []).append(ms)
    ratio = {k: ms / statistics.median(by_mode[mode_of(k)]) for k, ms in speeds.items()}
    return sorted(ratio, key=lambda k: (-ratio[k], k))[:WEAK_KINDS]


def _mmss(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def summary(sprint, history):
    sprints = history["sprints"]
    at = next((i for i, x in enumerate(sprints) if x is sprint), None)
    if at is not None:  # compare with the sprints before this one
        sprints = sprints[:at]
    mode = sprint["mode"]
    times = {}
    for q in sprint.get("questions", []):
        times.setdefault(q["kind"], []).append(q["ms"])
    slow = sorted(((statistics.median(v), k) for k, v in times.items()), reverse=True)[:3]
    slowest = "SLOWEST: " + (" · ".join(f"{k} {ms / 1000:.1f} s" for ms, k in slow) if slow else "—")
    if not sprint.get("complete"):
        return f"ARITHMETIC: {mode} · stopped at {_mmss(sprint.get('stopped', 0))} · score {sprint['score']}\n{slowest}"
    prior = [sp["score"] for sp in sprints  # only sprints of the same mode and length compare
             if sp["mode"] == mode and sp.get("seconds") == sprint["seconds"] and sp.get("complete")]
    best = str(max(prior)) if prior else "—"
    avg = f"{statistics.mean(prior[-5:]):.1f}" if prior else "—"
    return (f"ARITHMETIC: {mode} · {sprint['seconds']} s · score {sprint['score']} ({sprint.get('skipped', 0)} skipped)\n"
            f"BEST: {best} · LAST 5 AVERAGE: {avg}\n{slowest}")


# ---------------------------------------------------------------- the sprint

def deadline_left(start, seconds, now):
    """Seconds left by wall clock; a laptop that slept past the end has none."""
    return max(0.0, start + seconds - now)


def play(stdscr, mode, seconds):
    import curses
    curses.curs_set(1)
    curses.use_default_colors()
    try:
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
    except Exception:
        pass
    history = load_history()
    weak = weak_kinds(history) if mode == "weak" else None
    rng = random.Random()
    stdscr.timeout(200)  # redraw the clock while waiting for keys
    q = generate(mode, rng, weak)
    start = shown = time.time()
    typed, flash, score, skipped, done = "", "", 0, 0, []
    stopped = None

    def draw(left):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        head = f"ARITHMETIC · {mode}"
        right = f"score {score} · {_mmss(left)}"
        try:
            stdscr.addstr(0, 2, head, curses.A_BOLD | curses.color_pair(1))
            stdscr.addstr(0, max(2, w - len(right) - 2), right, curses.A_BOLD)
            line = f"{q['text']} {'≈' if q['estimate'] else '='} {typed}"
            stdscr.addstr(h // 2 - 1, max(2, (w - len(line)) // 2), line, curses.A_BOLD)
            if flash:
                stdscr.addstr(h // 2 + 1, max(2, (w - len(flash)) // 2), flash, curses.color_pair(3))
            keys = "type the answer" + (" · Enter submit" if q["estimate"] else "") + " · Tab skip · Esc stop"
            stdscr.addstr(h - 1, 2, keys[:w - 3], curses.A_DIM)
            stdscr.move(h // 2 - 1, min(w - 2, max(2, (w - len(line)) // 2) + len(line)))
        except curses.error:
            pass
        stdscr.refresh()

    def advance(correct):
        nonlocal q, typed, flash, shown, score, skipped
        if correct:
            done.append({"kind": q["kind"], "ms": int((time.time() - shown) * 1000)})
            score += 1
        else:
            skipped += 1
        q, typed, flash, shown = generate(mode, rng, weak), "", "", time.time()

    while True:
        left = deadline_left(start, seconds, time.time())
        if left <= 0:
            break
        draw(left)
        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue
        if deadline_left(start, seconds, time.time()) <= 0:
            break  # a key pressed after 0:00 does not count
        if ch == "\x1b":
            stopped = int(time.time() - start)
            break
        if ch in ("\t",):
            advance(False)
        elif ch in ("\n", "\r") or ch == curses.KEY_ENTER:
            if q["estimate"]:
                if accepts(typed, q, enter=True):
                    advance(True)
                elif typed:
                    flash = "not within 2%"
        elif ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            typed, flash = typed[:-1], ""
        elif isinstance(ch, str) and ch in "0123456789.-" and len(typed) < 12:
            typed, flash = typed + ch, ""
            if not q["estimate"] and accepts(typed, q):
                advance(True)

    sprint = {"date": time.strftime("%Y-%m-%d"), "time": time.strftime("%H:%M"), "mode": mode, "seconds": seconds,
              "complete": stopped is None, "score": score, "skipped": skipped, "questions": done}
    if stopped is not None:
        sprint["stopped"] = stopped
    save_sprint(sprint)  # before the end screen, so a closed popup loses nothing
    curses.curs_set(0)
    stdscr.erase()
    lines = summary(sprint, history).split("\n") + ["", "press any key"]
    for i, ln in enumerate(lines):
        try:
            stdscr.addstr(1 + i, 2, ln, curses.A_BOLD if i == 0 else 0)
        except curses.error:
            pass
    stdscr.refresh()
    curses.flushinp()
    curses.napms(1000)  # the learner is usually mid-answer at 0:00: keys typed now must not close this screen
    curses.flushinp()
    stdscr.timeout(-1)
    stdscr.get_wch()


def popup_command(mode, seconds, height, width="70"):
    inner = " ".join(shlex.quote(x) for x in (sys.executable, os.path.abspath(__file__), "play", mode,
                                                  "--seconds", str(seconds)))
    return ["tmux", "display-popup", "-E", "-w", width, "-h", height, "-T", " arith ", inner]


# ---------------------------------------------------------------- commands

def cmd_play(a):
    import curses
    load_history()  # a corrupt file is refused here, where the message can still be read
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(play, a.mode, a.seconds)


def cmd_run(a):
    if not os.environ.get("TMUX"):
        print(f'NO TMUX: run "python3 .claude/hooks/arith.py play {a.mode}" in another terminal, then /arith last')
        return
    before = len(load_history()["sprints"])
    proc = subprocess.run(popup_command(a.mode, a.seconds, "14"), capture_output=True, text=True)
    if proc.returncode != 0 and "too large" in (proc.stderr or ""):  # a short or narrow pane
        proc = subprocess.run(popup_command(a.mode, a.seconds, "90%", "90%"), capture_output=True, text=True)
    if proc.returncode != 0 and (proc.stderr or "").strip():
        print(f"POPUP FAILED: {proc.stderr.strip()}")
        return
    h = load_history()
    if len(h["sprints"]) <= before:
        print("NO SPRINT RECORDED")
        return
    print(summary(h["sprints"][-1], h))


def cmd_last(a):
    h = load_history()
    if not h["sprints"]:
        print("NO SPRINT RECORDED")
        return
    print(summary(h["sprints"][-1], h))


def cmd_history(a):
    h = load_history()
    for mode in ([a.mode] if a.mode else MODES):
        lengths = sorted({sp.get("seconds") for sp in h["sprints"] if sp["mode"] == mode and sp.get("complete")})
        for secs in lengths:
            scores = [sp["score"] for sp in h["sprints"]
                      if sp["mode"] == mode and sp.get("seconds") == secs and sp.get("complete")][-10:]
            print(f"{mode} {secs} s: {' '.join(map(str, scores))} · best {max(scores)} · "
                  f"average {statistics.mean(scores):.1f}")


def cmd_kinds(a):
    speeds = kind_speeds(load_history())
    for k in sorted(speeds, key=lambda k: -speeds[k]):
        if not a.mode or mode_of(k) == a.mode:
            print(f"{k} {speeds[k] / 1000:.1f} s")


def seconds_arg(text):
    n = int(text)
    if not 10 <= n <= 480:
        raise argparse.ArgumentTypeError("a sprint is 10 to 480 seconds")
    return n


def main(argv=None):
    p = argparse.ArgumentParser(prog="arith.py", description="Timed mental arithmetic sprints.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "play"):
        s = sub.add_parser(name)
        s.add_argument("mode", nargs="?", default="core", choices=MODES)
        s.add_argument("--seconds", type=seconds_arg, default=120)
    sub.add_parser("last")
    s = sub.add_parser("history")
    s.add_argument("mode", nargs="?", choices=MODES)
    s = sub.add_parser("kinds")
    s.add_argument("mode", nargs="?", choices=CONCRETE)
    a = p.parse_args(argv)
    {"run": cmd_run, "play": cmd_play, "last": cmd_last, "history": cmd_history, "kinds": cmd_kinds}[a.cmd](a)


if __name__ == "__main__":
    main()
